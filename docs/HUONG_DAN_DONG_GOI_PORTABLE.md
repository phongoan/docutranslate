# Hướng dẫn đóng gói DocuTranslate thành 1 file portable

DocuTranslate gồm backend Python (FastAPI) và giao diện web Vue. Giao diện được build sẵn vào
`docutranslate/static`, sau đó PyInstaller gom toàn bộ Python, thư viện, giao diện và template
vào **một file chạy duy nhất** (`.exe` trên Windows). Người dùng chỉ cần chép file đó sang máy
khác và nhấp đúp, không cần cài Python hay Node.js.

> PyInstaller không biên dịch chéo: muốn có file `.exe` cho Windows thì phải build trên Windows
> (hoặc dùng GitHub Actions, xem mục 5). Build trên macOS/Linux sẽ ra file chạy cho hệ đó.

## 1. Chuẩn bị (chỉ làm một lần)

| Công cụ | Phiên bản | Ghi chú |
|---|---|---|
| Python | 3.12 (xem `.python-version`) | Tích chọn "Add Python to PATH" khi cài |
| [uv](https://docs.astral.sh/uv/) | mới nhất | `pip install uv` hoặc `winget install astral-sh.uv` |
| Node.js | 20+ (xem `frontend/.nvmrc`) | Chỉ cần khi bạn sửa giao diện |
| UPX (tùy chọn) | bất kỳ | Nén file exe nhỏ hơn: `choco install upx` |

## 2. Build nhanh bằng script (Windows)

Mở PowerShell tại thư mục gốc của dự án và chạy:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1
```

Script sẽ: build lại giao diện (nếu có Node.js) → cài phụ thuộc bằng `uv` → chạy PyInstaller
với `lite.spec`. Kết quả nằm ở `dist\DocuTranslate-<phiên bản>-win.exe`.

Thêm `-SkipFrontend` nếu không sửa giao diện (dùng bản đã build sẵn trong `docutranslate/static`).

## 3. Build thủ công từng bước

```bash
# 3.1 Build giao diện (bỏ qua nếu không sửa thư mục frontend/)
cd frontend
npm ci
npm run build          # xuất ra ../docutranslate/static
cd ..

# 3.2 Cài phụ thuộc Python (bắt buộc kèm extra "mcp", lite.spec sẽ dừng nếu thiếu)
uv sync --locked --no-dev --extra mcp

# 3.3 Cài PyInstaller và đóng gói
uv pip install pyinstaller==6.22.2
uv run --no-sync pyinstaller lite.spec --noconfirm --clean
```

File chạy được tạo trong thư mục `dist/`:

- Windows: `lite.spec` → `DocuTranslate-<ver>-win.exe`
- macOS Apple Silicon: `lite_mac.spec`; macOS Intel: `lite_mac_x86_64.spec`

`lite.spec` đã cấu hình chế độ **one-file** (gom `a.binaries` và `a.datas` vào `EXE`, không có
`COLLECT`), nên chỉ có một file duy nhất.

## 4. Sử dụng file portable

1. Chép file `.exe` vào thư mục bất kỳ (USB, Desktop...).
2. (Tùy chọn) Đặt file `.env` **cùng thư mục với exe** để cấu hình sẵn, ví dụ:

   ```env
   DOCUTRANSLATE_BASE_URL=https://api.openai.com/v1
   DOCUTRANSLATE_API_KEY=sk-...
   DOCUTRANSLATE_MODEL_ID=gpt-4o-mini
   DOCUTRANSLATE_TO_LANG=Tiếng Việt
   DOCUTRANSLATE_PORT=8010
   ```

   Xem đầy đủ các biến trong `.env.example`. Ứng dụng tìm `.env` ở thư mục hiện tại, các thư mục
   cha, rồi đến thư mục chứa exe.
3. Nhấp đúp file exe. Cửa sổ console hiện địa chỉ, mặc định
   `http://127.0.0.1:8010` (nếu cổng bận sẽ tự chuyển sang cổng kế tiếp). Mở địa chỉ đó bằng
   trình duyệt. Giao diện mặc định là tiếng Việt và có thể đổi ngôn ngữ ở góc dưới bên trái.
4. Đóng cửa sổ console để tắt ứng dụng.

Lưu ý:

- Lần chạy đầu khởi động chậm hơn vì file one-file phải giải nén vào thư mục tạm.
- Windows Defender/SmartScreen có thể cảnh báo file exe chưa ký số: chọn "More info → Run anyway",
  hoặc ký số file nếu phân phối rộng.
- Muốn ẩn cửa sổ console, đổi `console=True` thành `console=False` trong `lite.spec`.
  Khi đó bạn sẽ không thấy log và phải tự mở trình duyệt.

## 5. Build tự động bằng GitHub Actions

Workflow `.github/workflows/build-windows.yml` (và `build-macos.yml`) chạy đúng các bước trên.
Vào tab **Actions → Build Windows Application → Run workflow**, đợi xong rồi tải artifact
`DocuTranslate-Windows`. Khi tạo Release, exe được đính kèm vào Release tự động.

## 6. Xử lý lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `Bản build thiếu phụ thuộc MCP...` | Chạy lại `uv sync --extra mcp` |
| Mở trình duyệt thấy trang trắng / thiếu giao diện | Chạy `npm run build` trong `frontend/` rồi đóng gói lại |
| `ModuleNotFoundError` khi chạy exe | Thêm module vào `hiddenimports` trong `lite.spec` |
| Cổng 8010 bị chiếm | Đặt `DOCUTRANSLATE_PORT` trong `.env` |
| Muốn chạy MCP | Exe đã kèm MCP, endpoint SSE: `http://127.0.0.1:<port>/mcp/sse` |
