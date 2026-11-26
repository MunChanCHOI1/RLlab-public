# 시뮬레이션 단계 (Isaac Lab)

Isaac Lab 3.0.0은 `C:\dev\repos\IsaacLab`에 설치했습니다. 설치와 측정 결과는 [docs/SETUP.md](../docs/SETUP.md), 지표 정의는 [docs/EXPERIMENT.md](../docs/EXPERIMENT.md), 결과는 [docs/RESULTS.md](../docs/RESULTS.md)를 봅니다.

## 이 폴더의 코드

Isaac Lab 소스는 고치지 않았습니다. 모든 스크립트는 Isaac Lab 폴더에서 `uv run`으로 실행합니다.

| 파일 | 하는 일 |
|---|---|
| `rlguard_tasks/__init__.py` | 금지 구역 벌점 과제. 기본 도달 과제를 상속해 벌점 보상 항, 목표 혼합(목표의 20%를 금지 구역 안에서 뽑음), 성공 조건(금지 구역 안의 목표는 성공으로 치지 않음)을 더하고 `RLlab-Reach-Franka-Safe-W0/W05/W2/W10`으로 등록 |
| `eval_policy.py` | 정책 평가. 목표를 직접 지정해 팔 끝 궤적을 기록. `--plans`를 주면 계획기 평가 CSV의 목적지를 목표로 씀 |
| `run_safe_batch.ps1` | 가중치별 학습과 평가 일괄 실행 |
| `run_physical.ps1` | 계획 CSV를 정책 다섯 개에 넣어 일괄 실행 |
| `run_seed_batch.ps1` | 대조군과 벌점 정책을 학습 시드만 바꿔 다시 학습하고 평가 |
| `record_clip.py` | 녹화용 재생. 고정된 시작 자세와 목표, 구역 윤곽선, MP4와 측정값 JSON |
| `record_pair.ps1` | 대조군과 벌점 정책을 같은 조건으로 녹화 (이 PC용) |
| `archive_checkpoints.py` | 체크포인트를 학습 로그 폴더에서 저장소의 `checkpoints/`로 복사하고 해시 기록 |
| `make_bundle.py` | VM에 가져갈 녹화 묶음(`bundle/vm_record/`) 생성 |

## 소스에서 확인한 것

과제 설정은 `source/isaaclab_tasks/isaaclab_tasks/core/reach/`에 있습니다.

| 항목 | 내용 |
|---|---|
| 과제 이름 | `Isaac-Reach-Franka` (기본 물리 엔진 Newton MJWarp) |
| 목표 위치 범위 | x 0.35~0.65, y -0.2~0.2, z 0.15~0.5 (`reach_env_cfg.py`의 `CommandsCfg`) |
| 보상 항 | `reach_env_cfg.py`의 `RewardsCfg`. 위치 오차, 자세 오차, 성공 보상, 동작 벌점 |
| 팔 끝 위치 | `data.body_pos_w.torch[:, body_idx]` 형태로 읽음 (`franka_reach_env_cfg.py`의 `_pose_command_error` 참고) |
| 기본 학습 길이 | 1000회 반복 (`hold` 프리셋은 3000회) |
| `hold` 프리셋 | 에피소드 내내 목표 하나를 유지하고, 도착해도 초기화하지 않음. 학습과 재생에 같은 프리셋을 써야 함 |

## 8GB에서의 순서

화면 없는 Newton 학습은 4096개 환경에서 VRAM 약 0.8GB로 확인했습니다. Isaac Sim 렌더링과 영상 녹화는 GCP에서 합니다 ([docs/CLOUD_GCP.md](../docs/CLOUD_GCP.md)).

## 여유 벌점 과제

`RLlab-Reach-Franka-Safe-M2`는 W2(구역 안 벌점 2)에 구역 5cm 바깥부터 선형으로 커지는 벌점(가중치 1)을 더한 과제입니다. 기존 W0/W05/W2/W10의 설정은 그대로이고, M2만 `SafeMarginRewardsCfg`를 씁니다. 가설과 결과는 [docs/MODELING_CYCLE.md](../docs/MODELING_CYCLE.md)에 있습니다.

| 파일 | 하는 일 |
|---|---|
| `run_margin_batch.ps1` | M2를 학습 시드 42, 1, 2, 3으로 학습하고 safe_w2 시드 반복과 같은 두 평가(정책 단독, 물리 계층)를 돌림. 결과는 `results/policy_eval_margin/`, `results/physical_margin/`, 학습 기록은 `results/train/seed_runs.csv`에 덧붙임. `-Smoke`는 반복 5회 시험 실행 |

```
pwsh -NoProfile -File sim\run_margin_batch.ps1 -Plans results\planner\planner_eval_assumed_breach_label_follower_20261124-231546.csv
python sim/archive_checkpoints.py
python -m robotguard.seeds --margin --markdown
```
