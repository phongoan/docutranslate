# Đóng gói DocuTranslate thành 1 file exe portable (Windows).
# Cách dùng: powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1 [-SkipFrontend]
param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-Step($Title, [scriptblock]$Action) {
    Write-Host "==> $Title" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "Bước thất bại: $Title (mã lỗi $LASTEXITCODE)" }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "Không tìm thấy 'uv'. Cài bằng: pip install uv  hoặc  winget install astral-sh.uv"
}

if (-not $SkipFrontend) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Push-Location frontend
        try {
            Invoke-Step "Cài phụ thuộc giao diện (npm ci)" { npm ci }
            Invoke-Step "Build giao diện vào docutranslate/static" { npm run build }
        } finally { Pop-Location }
    } else {
        Write-Warning "Không có Node.js, dùng giao diện đã build sẵn trong docutranslate/static."
    }
}

Invoke-Step "Cài phụ thuộc Python (kèm MCP)" { uv sync --locked --no-dev --extra mcp }
Invoke-Step "Cài PyInstaller" { uv pip install pyinstaller==6.22.2 }
Invoke-Step "Đóng gói bằng PyInstaller (lite.spec)" { uv run --no-sync pyinstaller lite.spec --noconfirm --clean }

$exe = Get-ChildItem dist -Filter *.exe | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host ""
Write-Host "Hoàn tất! File portable: $($exe.FullName)" -ForegroundColor Green
