# 벌점 과제를 가중치별로 차례로 학습하고, 같은 평가 스크립트로 평가한다.
# 실행: pwsh -NoProfile -File sim\run_safe_batch.ps1
# 진행 상황은 results\train\batch_status.log에 한 줄씩 쌓인다.
param(
    [string[]]$Variants = @('W0', 'W05', 'W2', 'W10'),
    [int]$NumEnvs = 4096
)

$Repo = Split-Path -Parent $PSScriptRoot
$Lab = 'C:\dev\repos\IsaacLab'
$TrainLogs = Join-Path $Repo 'results\train'
$EvalOut = Join-Path $Repo 'results\policy_eval'
$Status = Join-Path $TrainLogs 'batch_status.log'
New-Item -ItemType Directory -Force $TrainLogs, $EvalOut | Out-Null

# 긴 경로 문제 대응: 에셋 캐시를 짧은 경로에 둔다 (docs/SETUP.md 참고).
$env:TEMP = 'C:\dev\scratch\il'
$env:TMP = 'C:\dev\scratch\il'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = Join-Path $Repo 'sim'

function Write-Status([string]$Message) {
    "[$(Get-Date -Format 'HH:mm:ss')] $Message" | Add-Content -Path $Status -Encoding utf8
}

Set-Location $Lab
Write-Status "batch start: $($Variants -join ', ')"
foreach ($v in $Variants) {
    $tag = 'safe_' + $v.ToLower()
    Write-Status "train $v start"
    uv run isaaclab train --rl_library rsl_rl --task "RLlab-Reach-Franka-Safe-$v" `
        --external_callback rlguard_tasks.register --num_envs $NumEnvs *> (Join-Path $TrainLogs "reach_$tag.log")
    Write-Status "train $v exit=$LASTEXITCODE"

    $runRoot = Join-Path $Lab "logs\rsl_rl\reach_franka_$tag"
    $run = Get-ChildItem $runRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch 'smoke' } | Sort-Object Name | Select-Object -Last 1
    $ckpt = if ($run) { Join-Path $run.FullName 'model_999.pt' } else { $null }
    if ($ckpt -and (Test-Path $ckpt)) {
        uv run python (Join-Path $Repo 'sim\eval_policy.py') --checkpoint $ckpt --tag $tag *> (Join-Path $EvalOut "${tag}_run.log")
        Write-Status "eval $v exit=$LASTEXITCODE ckpt=$ckpt"
    } else {
        Write-Status "eval $v skipped: checkpoint not found under $runRoot"
    }
}
Write-Status 'batch done'
