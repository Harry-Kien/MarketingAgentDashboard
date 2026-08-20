# Cài đặt từ đầu trên một máy trống.
#
#     git clone --recurse-submodules <repo>
#     cd Marketing
#     .\scripts\cai_dat.ps1
#
# Script này KHÔNG tự tạo tài khoản, không tự điền khoá API, và không tự
# khởi động dịch vụ bên thứ ba cần đăng nhập. Nó dựng phần dựng được và
# NÓI RÕ phần còn lại — im lặng bỏ qua một bước là để người cài tưởng đã
# xong trong khi hệ thống thiếu một nửa.

$ErrorActionPreference = "Stop"
$goc = Split-Path -Parent $PSScriptRoot
Set-Location $goc

function Buoc($n, $t) { Write-Host "`n[$n] $t" -ForegroundColor Cyan }
function Xong($t)      { Write-Host "    $t" -ForegroundColor Green }
function Can($t)       { Write-Host "    CẦN LÀM: $t" -ForegroundColor Yellow }

Buoc 1 "Kiểm điều kiện"
foreach ($lenh in @("python", "docker", "git")) {
    if (-not (Get-Command $lenh -ErrorAction SilentlyContinue)) {
        Write-Host "    THIẾU: $lenh" -ForegroundColor Red
        exit 1
    }
}
Xong "python, docker, git đều có"

Buoc 2 "Submodule (ZaloCRM)"
# ZaloCRM là submodule chứ không phải bản chép: mã AGPL nằm trong repo của
# họ, dưới giấy phép của họ. Xem chú thích trong .gitignore.
if (-not (Test-Path "ZaloCRM/package.json")) {
    git submodule update --init --recursive
}
if (Test-Path "ZaloCRM/package.json") { Xong "ZaloCRM đã có" }
else { Can "git submodule update --init --recursive" }

Buoc 3 "Môi trường Python"
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -q --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
Xong "thư viện đã cài (phiên bản ghim trong requirements.txt)"

Buoc 4 "Cấu hình"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Xong ".env tạo từ bản mẫu"
    Can "mở .env điền GCP_PROJECT_ID và đổi WEBHOOK_SECRET"
} else {
    Xong ".env đã có"
    $mau = Select-String -Path ".env" -Pattern "doi-chuoi-nay-di|your-gcp-project-id" -Quiet
    if ($mau) { Can "trong .env còn giá trị mẫu chưa đổi — grep 'doi-chuoi-nay-di'" }
}

Buoc 5 "Hạ tầng"
docker compose up -d
Xong "Postgres đã chạy"

Buoc 6 "Cơ sở dữ liệu và dữ liệu mẫu"
& .\.venv\Scripts\python.exe -m scripts.demo_seed
& .\.venv\Scripts\python.exe -m scripts.ingest
Xong "bảng, danh mục và kho tri thức đã nạp"

Buoc 7 "Kiểm thử"
& .\.venv\Scripts\python.exe -m pytest tests/ -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "    KIỂM THỬ HỎNG — dừng ở đây, đừng chạy tiếp" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== CÒN LẠI, PHẢI LÀM BẰNG TAY ===" -ForegroundColor Yellow
Write-Host @"
    1. Tài khoản đăng nhập dashboard:
         .\.venv\Scripts\python.exe -m scripts.tao_tai_khoan admin "mật khẩu mạnh" --quan-tri

    2. Xác thực Google Cloud (cho model và embedding):
         gcloud auth application-default login

    3. Zalo — quét QR trong ZaloCRM rồi nối vào hệ thống:
         docker compose -f ZaloCRM/docker-compose.yml up -d
         .\.venv\Scripts\python.exe -m scripts.zalo_link

    4. Chatwoot (tuỳ chọn, cho Facebook/Instagram/web):
         xem docs/phan-phoi-noi-dung.md

    Chạy hệ thống:
         .\.venv\Scripts\python.exe -m uvicorn agent.main:app --host 127.0.0.1 --port 8000
"@ -ForegroundColor Gray
