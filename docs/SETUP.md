# 환경 준비

2026-11-24에 공식 문서를 확인해 정리했습니다. 설치 직전에 원문을 다시 확인하세요. 문서를 요약으로만 확인한 항목은 "(요약 확인)"으로 표시했습니다.

## 이 PC에서 확인한 것

| 항목 | 상태 |
|---|---|
| Python | 3.12.10 설치됨 (Isaac Lab 3.0 요구 버전과 일치) |
| uv | 0.12.15 설치됨 |
| git | 설치됨 |
| GPU | RTX 5060 Laptop, VRAM 8151MiB |
| NVIDIA 드라이버 | 616.92 (문서 권장 595.97보다 높음) |
| RAM | 31.3GB |
| 디스크 여유 | 약 380GB |
| Windows 긴 경로 | 꺼져 있음 (아래 "긴 경로 문제" 참고) |

## 설치와 측정 결과 (2026-11-24)

Isaac Lab 3.0.0을 `C:\dev\repos\IsaacLab`에 받았습니다 (main, 커밋 `99a3acd`). 의존성 170개, 가상 환경 4.5GB이며 Isaac Sim은 설치하지 않았습니다.

화면 없이 Newton(MJWarp)으로 짧게 학습하며 VRAM 최댓값을 쟀습니다. 각 조건 1회 실행, 2초 간격 측정입니다.

| 과제 | 환경 수 | 반복 | 학습 시간 | VRAM 최댓값 |
|---|---|---|---|---|
| Isaac-Cartpole-Direct | 1024 | 30 | 36초 | 약 250MiB |
| Isaac-Reach-Franka | 1024 | 40 | 65초 | 약 340MiB |
| Isaac-Reach-Franka | 4096 | 40 | 40초 | 약 770MiB |

- VRAM은 `nvidia-smi`와 Windows 성능 카운터 두 방식으로 쟀고, 도달 과제에서 두 값이 일치했습니다 (4096개: 772MiB와 776MiB).
- 도달 과제의 기본 학습 길이는 1000회 반복입니다. 4096개 환경에서 반복당 약 0.5초였으므로 전체 학습은 8~9분으로 예상합니다. 40회 반복 1회 측정에서 계산한 값이라 실제와 다를 수 있습니다.
- 결론: 정책 학습은 이 PC로 충분합니다. Isaac Sim 렌더링은 이 PC에서 시험하지 않았고 GCP에서 하기로 했습니다.

## 기본 정책 전체 학습 (2026-11-24, 1회 실행)

```powershell
uv run isaaclab train --rl_library rsl_rl --task Isaac-Reach-Franka --num_envs 4096
```

| 항목 | 값 |
|---|---|
| 반복 | 1000회 (기본값) |
| 학습 시간 | 9분 33초 (반복당 약 0.57초. 40회 측정에서 예상한 8~9분보다 조금 김) |
| 마지막 반복의 성공 종료 비율 | 1.0000 (시간 초과 0.0000) |
| 마지막 반복의 위치 오차 | 0.046m |
| 마지막 반복의 자세 오차 | 0.185rad |
| 평균 에피소드 길이 | 약 36스텝 |
| 체크포인트 | `C:\dev\repos\IsaacLab\logs\rsl_rl\reach_franka\2026-11-24_21-02-13\model_999.pt` |
| 로그 | `results/train/reach_baseline.log` |

읽을 때 주의할 점:

- 이 과제는 위치 오차 0.05m, 자세 오차 0.2rad 안에 들어오면 성공으로 보고 에피소드를 끝냅니다. 위치 오차 0.046m는 "성공 기준에 닿는 순간 끝난다"는 뜻에 가깝고, 정책이 낼 수 있는 최종 정밀도를 뜻하지 않습니다.
- 학습 중 기록된 값이며, 학습이 끝난 정책을 따로 재생해 평가한 값은 아닙니다. 시드 1개, 1회 실행입니다.
- 금지 구역의 반 크기를 0.05m로 잡았으므로, 구역 중심을 목표로 받은 정책이 성공하면 팔 끝은 구역 안에 있게 됩니다.

## 긴 경로 문제

첫 실행은 에셋을 내려받다가 실패했습니다. 에셋 캐시가 임시 폴더 아래에 URL 구조 그대로 저장되는데, 경로가 269자가 되어 Windows 한도(260자)를 넘었기 때문입니다.

- **임시 대응 (지금 쓰는 방법)**: 실행 전에 임시 폴더를 짧은 경로로 바꿉니다. 같은 파일이 253자가 되어 통과하지만 여유가 7자뿐이라 다른 에셋에서 다시 걸릴 수 있습니다.

```powershell
$env:TEMP = 'C:\dev\scratch\il'; $env:TMP = 'C:\dev\scratch\il'
```

- **근본 대응**: 아래 "설치 순서 2"의 긴 경로 허용을 관리자 PowerShell에서 실행합니다.

## 알아둘 것

- `uv run isaaclab list_envs --show_presets`는 이 PC에서 9분 46초가 걸렸습니다. 과제 이름은 소스에서 찾는 편이 빠릅니다.
- 도달 과제 이름은 `Isaac-Reach-Franka`이고 기본 물리 엔진이 Newton입니다.
- 목표 위치 범위는 x 0.35~0.65, y -0.2~0.2, z 0.15~0.5이며 `data/scene.json`의 구역 좌표가 모두 이 안에 있습니다.
- `presets=hold`를 주면 에피소드 내내 목표 하나를 유지합니다. 3단계 연결에 쓸 수 있습니다 (기본 3000회 반복, 학습과 재생에 같은 프리셋 필요).

## 버전

- Isaac Lab 3.0.0, Isaac Sim 6.2.0, Python 3.12. Isaac Sim 5.1 이하는 지원하지 않습니다.
- Isaac Lab 3.0은 Newton 물리 엔진을 기본으로 설치하고, Isaac Sim은 선택 사항입니다.
- 설치 방식이 uv 기반으로 바뀌었습니다. 예전 글의 `isaaclab.bat --install` 방식은 현재 문서에 없습니다.

## 8GB VRAM 대응

Isaac Sim의 공식 최소 사양은 RTX 4080, VRAM 16GB, RAM 32GB입니다 (요약 확인). 문서는 최소 사양 미만에서 일부 예제가 돌지 않을 수 있다고 적고 있습니다. 8GB에서의 동작은 보장되지 않으므로 아래 순서로 진행합니다.

1. **학습은 Newton으로, 화면 없이.** 문서에 "화면 없는 Newton 시뮬레이션은 RTX 하드웨어가 필요 없다"고 되어 있어 8GB에서 가장 안전합니다. 환경 개수(`--num_envs`)를 작게 시작해 늘립니다.
2. **Isaac Sim은 영상 촬영에만.** 학습한 정책을 재생해 영상을 찍는 마지막 단계에서만 Isaac Sim 렌더링을 시도합니다.
3. **Isaac Sim이 안 뜨면** Newton 뷰어(`--viz newton`)로 영상을 찍고, README에 "Isaac Lab + Newton, Isaac Sim 렌더링은 사양 문제로 미사용"이라고 적습니다. 클라우드 GPU를 빌리는 방법도 있습니다.

실제로는 1번과 3번의 앞부분까지 진행했습니다. Franka 도달 과제는 Newton이 기본이라 그대로 학습됐고, Newton 화면 녹화도 이 PC에서 됐습니다. Isaac Sim 렌더링은 이 PC에서 시도하지 않았습니다.

## 설치 순서

### 1. 드라이버

문서가 권장하는 Windows 드라이버는 595.97입니다. 현재 버전은 아래로 확인합니다.

```powershell
nvidia-smi
```

### 2. 긴 경로 허용 (관리자 PowerShell, 시스템 설정 변경)

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
```

### 3. Isaac Lab 받기

이 폴더와 나란히 `C:\dev\repos\IsaacLab`에 받는 것을 권장합니다.

```powershell
git clone https://github.com/isaac-sim/IsaacLab.git --branch main C:\dev\repos\IsaacLab
```

`main`은 계속 바뀝니다. 이 프로젝트의 결과는 커밋 `99a3acd776f47fbcece4413f3c1d63f02b6979e2`에서 얻었으므로, 같은 결과를 다시 얻으려면 받은 뒤 이 커밋으로 맞춥니다.

### 4. Isaac Sim 없이 동작 확인

`IsaacLab` 폴더 안에서 실행합니다. 첫 실행 때 의존성을 내려받습니다.

```powershell
uv run isaaclab list_envs --show_presets
```

```powershell
uv run isaaclab train --rl_library rsl_rl --task Isaac-Cartpole-Direct physics=newton_mjwarp
```

```powershell
uv run isaaclab play --rl_library rsl_rl --task Isaac-Cartpole-Direct --viz newton
```

### 5. Isaac Sim 추가 (용량 큼, 8GB에서 동작 미보장)

```powershell
uv sync --extra isaacsim
```

```powershell
uv run --extra isaacsim isaaclab train --rl_library rsl_rl --task Isaac-Cartpole-Direct physics=isaacsim_physx
```

첫 실행 때 확장 기능을 내려받고 EULA 동의를 묻습니다.

## 설치 후 확인할 것

- [x] Franka 도달 과제의 정확한 이름: `Isaac-Reach-Franka`
- [x] 그 과제가 Newton에서 도는지: 기본값이 Newton이며 학습됨
- [x] 8GB에서 돌릴 수 있는 환경 수와 학습 시간: 4096개에서 약 770MiB
- [ ] Isaac Sim 렌더링: 이 PC에서는 시험하지 않음. GCP에서 진행 ([CLOUD_GCP.md](CLOUD_GCP.md))
- [x] 1000회 전체 학습의 실제 소요 시간: 9분 33초
- [x] 학습된 정책을 따로 재생해 잰 도달 정확도와 궤적: [RESULTS.md](RESULTS.md)
- [x] 이 PC에서 영상 녹화: Newton 화면(`viz:newton`)으로 MP4가 만들어짐. `uv run --extra video`로 moviepy가 가상 환경에 추가됨 (2026-11-25)

## 출처

- [Isaac Lab 설치](https://isaac-sim.github.io/IsaacLab/main/source/isaaclab/installation.html)
- [Isaac Lab 빠른 시작](https://isaac-sim.github.io/IsaacLab/main/source/isaaclab/quickstart.html)
- [Isaac Sim 요구 사양](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html)
