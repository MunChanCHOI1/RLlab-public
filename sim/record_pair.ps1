# 대조군(safe_w0)과 벌점 정책(safe_w2)을 같은 시작 자세와 목표로 재생해 영상을 남긴다 (Windows, 이 PC용).
# 실행: pwsh -NoProfile -File sim\record_pair.ps1 [-Targets zone_b,zone_x] [-Source viz:newton] [-OutDir results\video]
# Linux VM에서는 bundle/ 안의 record_pair.sh를 쓴다 (sim/make_bundle.py가 만든다).
param(
    [string[]]$Targets = @('zone_b', 'zone_x'),
    [string]$Source = 'viz:newton',
    [string]$OutDir = '',
    [string]$Lab = 'C:\dev\repos\IsaacLab'
)

$Repo = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $Repo 'results\video' }
New-Item -ItemType Directory -Force $OutDir | Out-Null
$Status = Join-Path $OutDir 'batch_status.log'

# 정책 이름과 학습 실행 폴더 (docs/RESULTS.md의 정책 표와 같다).
$Policies = [ordered]@{
    safe_w0 = 'reach_franka_safe_w0\2026-11-24_21-24-26'
    safe_w2 = 'reach_franka_safe_w2\2026-11-24_21-44-57'
}

# 긴 경로 문제 대응: 에셋 캐시를 짧은 경로에 둔다 (docs/SETUP.md 참고).
$env:TEMP = 'C:\dev\scratch\il'
$env:TMP = 'C:\dev\scratch\il'
$env:PYTHONIOENCODING = 'utf-8'

function Write-Status([string]$Message) {
    "[$(Get-Date -Format 'HH:mm:ss')] $Message" | Add-Content -Path $Status -Encoding utf8
}

Set-Location $Lab
Write-Status "batch start: source=$Source targets=$($Targets -join ',')"
foreach ($target in $Targets) {
    foreach ($tag in $Policies.Keys) {
        $ckpt = Join-Path $Lab (Join-Path 'logs\rsl_rl' (Join-Path $Policies[$tag] 'model_999.pt'))
        uv run --extra video python (Join-Path $Repo 'sim\record_clip.py') --checkpoint $ckpt --tag $tag `
            --target $target --source $Source --out $OutDir *> (Join-Path $OutDir "${tag}_${target}_run.log")
        Write-Status "record $tag $target exit=$LASTEXITCODE"
    }
}
Write-Status 'batch done'
