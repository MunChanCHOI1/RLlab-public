# 여유 벌점 과제(RLlab-Reach-Franka-Safe-M2)를 학습 시드별로 학습하고, safe_w2 시드 반복과 같은 두 평가를 돌린다.
# 실행: pwsh -NoProfile -File sim\run_margin_batch.ps1 -Plans <가정 조건 계획 CSV> [-Seeds 42,1,2,3]
# 시험 실행: ... -Smoke (반복 5회, 환경 256개, 학습 기록은 reach_franka_safe_m2_smoke, 결과는 results\margin_smoke)
# 학습 설정은 run_seed_batch.ps1과 같다 (환경 4096개, 1000회 반복, --seed만 다름). 보상만 다르다.
# 정책 이름: 시드 42는 safe_m2, 나머지는 safe_m2_s<시드> (robotguard.seeds의 이름 규칙).
# 진행 상황: results\train\margin_batch_status.log, 시드와 학습 폴더의 대응: results\train\seed_runs.csv에 덧붙인다.
param(
    [Parameter(Mandatory = $true)][string]$Plans,
    [int[]]$Seeds = @(42, 1, 2, 3),
    [int]$NumEnvs = 4096,
    [switch]$Smoke,
    [string]$Lab = 'C:\dev\repos\IsaacLab'
)

$Repo = Split-Path -Parent $PSScriptRoot
$Plans = (Resolve-Path $Plans).Path
$TrainLogs = Join-Path $Repo 'results\train'
$Variant = 'M2'
$Experiment = 'reach_franka_safe_m2'
$ExtraArgs = @()
if ($Smoke) {
    $Experiment = 'reach_franka_safe_m2_smoke'
    $NumEnvs = 256
    $ExtraArgs = @('--max_iterations', '5', '--experiment_name', $Experiment)
    $SmokeRoot = Join-Path $Repo 'results\margin_smoke'
    $TrainLogs = $SmokeRoot
    $EvalOut = Join-Path $SmokeRoot 'policy_eval'
    $PhysOut = Join-Path $SmokeRoot 'physical'
    $Runs = Join-Path $SmokeRoot 'seed_runs.csv'
} else {
    $EvalOut = Join-Path $Repo 'results\policy_eval_margin'
    $PhysOut = Join-Path $Repo 'results\physical_margin'
    $Runs = Join-Path $TrainLogs 'seed_runs.csv'
}
$Status = Join-Path $TrainLogs 'margin_batch_status.log'
New-Item -ItemType Directory -Force $TrainLogs, $EvalOut, $PhysOut | Out-Null
if (-not (Test-Path $Runs)) { 'policy,variant,seed,run_dir' | Set-Content -Path $Runs -Encoding utf8 }

# 긴 경로 문제 대응: 에셋 캐시를 짧은 경로에 둔다 (docs/SETUP.md 참고).
$env:TEMP = 'C:\dev\scratch\il'
$env:TMP = 'C:\dev\scratch\il'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = Join-Path $Repo 'sim'

function Write-Status([string]$Message) {
    "[$(Get-Date -Format 'HH:mm:ss')] $Message" | Add-Content -Path $Status -Encoding utf8
}

Set-Location $Lab
Write-Status "batch start: variant=$Variant seeds=$($Seeds -join ',') smoke=$([bool]$Smoke) plans=$Plans"
foreach ($seed in $Seeds) {
    $tag = if ($seed -eq 42) { 'safe_m2' } else { "safe_m2_s$seed" }
    $runRoot = Join-Path $Lab "logs\rsl_rl\$Experiment"
    $before = @(Get-ChildItem $runRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object Name)

    Write-Status "train $tag start"
    uv run isaaclab train --rl_library rsl_rl --task "RLlab-Reach-Franka-Safe-$Variant" `
        --external_callback rlguard_tasks.register --num_envs $NumEnvs --seed $seed @ExtraArgs *> (Join-Path $TrainLogs "reach_$tag.log")
    Write-Status "train $tag exit=$LASTEXITCODE"

    # 이번 학습이 새로 만든 폴더만 고른다 (기존 폴더를 잘못 집지 않게).
    $new = @(Get-ChildItem $runRoot -Directory -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Name } | Sort-Object Name)
    $ckpt = $null
    if ($new.Count -eq 1) {
        $ckpt = Get-ChildItem $new[0].FullName -Filter 'model_*.pt' |
            Sort-Object { [int]($_.BaseName -replace 'model_', '') } | Select-Object -Last 1 | ForEach-Object FullName
    }
    if (-not $ckpt -or (-not $Smoke -and (Split-Path -Leaf $ckpt) -ne 'model_999.pt')) {
        Write-Status "eval $tag skipped: expected exactly one new run with model_999.pt (found $($new.Count), ckpt=$ckpt)"
        continue
    }
    "$tag,$Variant,$seed,$($new[0].FullName)" | Add-Content -Path $Runs -Encoding utf8

    uv run python (Join-Path $Repo 'sim\eval_policy.py') --checkpoint $ckpt --tag $tag --out $EvalOut *> (Join-Path $EvalOut "${tag}_run.log")
    Write-Status "eval $tag exit=$LASTEXITCODE"
    uv run python (Join-Path $Repo 'sim\eval_policy.py') --checkpoint $ckpt --tag $tag --plans $Plans --out $PhysOut *> (Join-Path $PhysOut "${tag}_run.log")
    Write-Status "physical $tag exit=$LASTEXITCODE"
}
Write-Status 'batch done'
