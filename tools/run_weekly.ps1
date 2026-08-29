# 발주레이더 주간 발행 (로컬 폴백): 수집 → 리포트 → 커밋 → 푸시
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
git pull --rebase
python tools/radar.py all --days 8
git add -A
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "주간 리포트 발행 (로컬)"
    git push
    Write-Host "발행 완료. 구독자 이메일 발송을 잊지 마세요."
} else {
    Write-Host "변경 없음."
}
