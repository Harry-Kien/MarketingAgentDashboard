# ============================================================
#  Khởi động Marketing Agent — chạy một lệnh là xong
#      .\start.ps1            chạy bình thường
#      .\start.ps1 -Demo      nạp thêm dữ liệu trình diễn
# ============================================================
param([switch]$Demo)

$ErrorActionPreference = "Stop"
$py = ".\.venv\Scripts\python.exe"

Write-Host "[1/5] Kiem tra Docker..." -ForegroundColor Cyan
docker ps *> $null
if (-not $?) {
    Write-Host "  Docker chua chay. Mo Docker Desktop, doi bieu tuong het nhap nhay roi chay lai." -ForegroundColor Red
    exit 1
}

Write-Host "[2/5] Dung Postgres + Langfuse..." -ForegroundColor Cyan
docker compose up -d
if (-not $?) { Write-Host "  docker compose that bai." -ForegroundColor Red; exit 1 }

Write-Host "[3/5] Doi Postgres san sang..." -ForegroundColor Cyan
$ready = $false
foreach ($i in 1..40) {
    docker compose exec -T db pg_isready -U agent -d marketing_agent *> $null
    if ($?) { $ready = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $ready) { Write-Host "  Postgres khong len sau 80 giay." -ForegroundColor Red; exit 1 }

Write-Host "[4/5] Kiem tra cau hinh..." -ForegroundColor Cyan
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
$envText = Get-Content ".env" -Raw
if ($envText -match "GCP_PROJECT_ID=your-gcp-project-id") {
    Write-Host "  CANH BAO: chua dien GCP_PROJECT_ID trong .env." -ForegroundColor Yellow
    Write-Host "  Dashboard van chay, nhung agent va RAG se khong tra loi duoc." -ForegroundColor Yellow
}

if ($Demo) {
    Write-Host "  Nap du lieu trinh dien..." -ForegroundColor Cyan
    & $py -m scripts.demo_seed
}

Write-Host "[5/5] Chay ung dung tren http://localhost:8000" -ForegroundColor Green
Write-Host ""
& $py -m uvicorn agent.main:app --reload --host 127.0.0.1 --port 8000
