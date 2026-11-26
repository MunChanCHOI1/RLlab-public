# 계획기 평가 CSV의 계획을 정책 다섯 개에 차례로 넣어 팔 끝 궤적을 기록한다.
# 실행: pwsh -NoProfile -File sim\run_physical.ps1 -Plans <계획기 평가 CSV>
# 집계: python -m robotguard.physical --dir <OutDir>
param(
    [Parameter(Mandatory = $true)][string]$Plans,
    [string]$OutDir = ''
)

$Repo = Split-Path -Parent $PSScriptRoot
$Lab = 'C:\dev\repos\IsaacLab'
if (-not $OutDir) { $OutDir = Join-Path $Repo 'results\physical' }
$Plans = (Resolve-Path $Plans).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null
$Status = Join-Path $OutDir 'batch_status.log'

# 정책 이름과 학습 실행 폴더 (docs/RESULTS.md의 정책 표와 같다).
$Policies = [ordered]@{
    baseline = 'reach_franka\2026-11-24_21-02-13'
    safe_w0  = 'reach_franka_safe_w0\2026-11-24_21-24-26'
    safe_w05 = 'reach_franka_safe_w05\2026-11-24_21-34-43'
    safe_w2  = 'reach_franka_safe_w2\2026-11-24_21-44-57'
    safe_w10 = 'reach_franka_safe_w10\2026-11-24_21-56-25'
}

# 긴 경로 문제 대응: 에셋 캐시를 짧은 경로에 둔다 (docs/SETUP.md 참고).
$env:TEMP = 'C:\dev\scratch\il'
$env:TMP = 'C:\dev\scratch\il'
$env:PYTHONIOENCODING = 'utf-8'

function Write-Status([string]$Message) {
    "[$(Get-Date -Format 'HH:mm:ss')] $Message" | Add-Content -Path $Status -Encoding utf8
}

Set-Location $Lab
Write-Status "batch start: plans=$Plans"
foreach ($tag in $Policies.Keys) {
    $ckpt = Join-Path $Lab (Join-Path 'logs\rsl_rl' (Join-Path $Policies[$tag] 'model_999.pt'))
    if (-not (Test-Path $ckpt)) {
        Write-Status "eval $tag skipped: checkpoint not found: $ckpt"
        continue
    }
    uv run python (Join-Path $Repo 'sim\eval_policy.py') --checkpoint $ckpt --tag $tag --plans $Plans --out $OutDir *> (Join-Path $OutDir "${tag}_run.log")
    Write-Status "eval $tag exit=$LASTEXITCODE"
}
Write-Status 'batch done'
