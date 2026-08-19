# ============================================================
#  Thiet lap Vertex AI — chay MOT LAN
#      .\setup-vertex.ps1
#
#  Script tu tim gcloud (khong can PATH), dang nhap, chon project,
#  ghi vao .env va kiem tra ket noi.
# ============================================================

$ErrorActionPreference = "Stop"

function Find-Gcloud {
    # 1. PATH (neu terminal moi da co)
    $cmd = Get-Command gcloud -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    # 2. Cac vi tri winget/installer hay dung
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'),
        'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd',
        'C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

Write-Host "[1/5] Tim gcloud..." -ForegroundColor Cyan
$gcloud = Find-Gcloud
if (-not $gcloud) {
    Write-Host "  Khong thay gcloud. Cai bang lenh sau roi chay lai:" -ForegroundColor Red
    Write-Host "    winget install --id Google.CloudSDK -e" -ForegroundColor Yellow
    exit 1
}
Write-Host "  $gcloud" -ForegroundColor Green

Write-Host "[2/5] Dang nhap Application Default Credentials..." -ForegroundColor Cyan
Write-Host "  Trinh duyet se mo ra. Dang nhap bang tai khoan Google co quyen tren GCP project." -ForegroundColor Yellow
& $gcloud auth application-default login
if (-not $?) { Write-Host "  Dang nhap that bai." -ForegroundColor Red; exit 1 }

Write-Host "[3/5] Danh sach project cua ban:" -ForegroundColor Cyan
& $gcloud projects list --format="table(projectId,name)" 2>$null

$projectId = Read-Host "`n  Nhap PROJECT ID muon dung"
if ([string]::IsNullOrWhiteSpace($projectId)) {
    Write-Host "  Chua nhap project id." -ForegroundColor Red; exit 1
}

Write-Host "[4/5] Ghi vao .env..." -ForegroundColor Cyan
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
$lines = Get-Content ".env"
$patched = $false
$out = foreach ($line in $lines) {
    if ($line -match '^GCP_PROJECT_ID=') { $patched = $true; "GCP_PROJECT_ID=$projectId" }
    else { $line }
}
if (-not $patched) { $out += "GCP_PROJECT_ID=$projectId" }
$out | Set-Content ".env" -Encoding utf8
Write-Host "  GCP_PROJECT_ID=$projectId" -ForegroundColor Green

# Quota project cho ADC — tranh loi 'user project not set' khi goi Vertex
& $gcloud auth application-default set-quota-project $projectId 2>$null

Write-Host "[5/5] Kiem tra goi duoc Claude tren Vertex..." -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" -c @"
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from agent.config import get_settings
get_settings.cache_clear()
s = get_settings()
print(f'  project={s.gcp_project_id} region={s.gcp_region} model={s.model_chat}')
from anthropic import AnthropicVertex
c = AnthropicVertex(project_id=s.gcp_project_id, region=s.gcp_region)
r = c.messages.create(model=s.model_chat, max_tokens=32,
                      messages=[{'role':'user','content':'Tra loi dung hai chu: San sang'}])
print('  Claude tra loi:', ''.join(b.text for b in r.content if b.type=='text').strip())
print('  THANH CONG - Vertex da san sang.')
"@

Write-Host ""
Write-Host "Buoc tiep theo - nap tai lieu vao co so tri thuc:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\python.exe -m scripts.ingest data/knowledge"
Write-Host "Roi khoi dong lai app de nap cau hinh moi:" -ForegroundColor Green
Write-Host "  .\start.ps1"
