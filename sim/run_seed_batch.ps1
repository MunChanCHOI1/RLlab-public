# 대조군(W0)과 벌점 정책(W2)을 학습 시드만 바꿔 다시 학습하고, 기존과 같은 두 평가를 돌린다.
# 실행: pwsh -NoProfile -File sim\run_seed_batch.ps1 -Plans <가정 조건 계획 CSV> [-Seeds 1,2,3]
# 기존 정책(safe_w0, safe_w2)은 시드 42다. 평가 환경의 시드는 바꾸지 않으므로 평가 에피소드는 기존과 같다.
# 진행 상황: results\train\seed_batch_status.log, 시드와 학습 폴더의 대응: results\train\seed_runs.csv
param(
    [Parameter(Mandatory = $true)][string]$Plans,
    [int[]]$Seeds = @(1, 2, 3),
    [string[]]$Variants = @('W0', 'W2'),
    [int]$NumEnvs = 4096,
    [string]$Lab = 'C:\dev\repos\IsaacLab'
)

$Repo = Split-Path -Parent $PSScriptRoot
$Plans = (Resolve-Path $Plans).Path
$TrainLogs = Join-Path $Repo 'results\train'
$EvalOut = Join-Path $Repo 'results\policy_eval_seeds'
$PhysOut = Join-Path $Repo 'results\physical_seeds'
$Status = Join-Path $TrainLogs 'seed_batch_status.log'
$Runs = Join-Path $TrainLogs 'seed_runs.csv'
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
Write-Status "batch start: variants=$($Variants -join ',') seeds=$($Seeds -join ',')"
foreach ($seed in $Seeds) {
    foreach ($v in $Variants) {
        $tag = "safe_$($v.ToLower())_s$seed"
        $runRoot = Join-Path $Lab "logs\rsl_rl\reach_franka_safe_$($v.ToLower())"
        $before = @(Get-ChildItem $runRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object Name)

        Write-Status "train $tag start"
        uv run isaaclab train --rl_library rsl_rl --task "RLlab-Reach-Franka-Safe-$v" `
            --external_callback rlguard_tasks.register --num_envs $NumEnvs --seed $seed *> (Join-Path $TrainLogs "reach_$tag.log")
        Write-Status "train $tag exit=$LASTEXITCODE"

        # 이번 학습이 새로 만든 폴더만 고른다 (기존 폴더를 잘못 집지 않게).
        $new = @(Get-ChildItem $runRoot -Directory | Where-Object { $before -notcontains $_.Name } | Sort-Object Name)
        $ckpt = if ($new.Count -eq 1) { Join-Path $new[0].FullName 'model_999.pt' } else { $null }
        if (-not $ckpt -or -not (Test-Path $ckpt)) {
            Write-Status "eval $tag skipped: expected exactly one new run with model_999.pt (found $($new.Count))"
            continue
        }
        "$tag,$v,$seed,$($new[0].FullName)" | Add-Content -Path $Runs -Encoding utf8

        uv run python (Join-Path $Repo 'sim\eval_policy.py') --checkpoint $ckpt --tag $tag --out $EvalOut *> (Join-Path $EvalOut "${tag}_run.log")
        Write-Status "eval $tag exit=$LASTEXITCODE"
        uv run python (Join-Path $Repo 'sim\eval_policy.py') --checkpoint $ckpt --tag $tag --plans $Plans --out $PhysOut *> (Join-Path $PhysOut "${tag}_run.log")
        Write-Status "physical $tag exit=$LASTEXITCODE"
    }
}
Write-Status 'batch done'
