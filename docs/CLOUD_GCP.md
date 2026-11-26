# GCP에서 Isaac Sim 돌리기

이 PC(VRAM 8GB)에서 안 되는 Isaac Sim 렌더링과 영상 녹화를 GCP에서 하는 절차입니다. NVIDIA와 Google 공식 문서를 기준으로 했고, VM에서 1회 실행했습니다.

## 실행 기록 (2026-11-25, 1회)

| 항목 | 값 |
|---|---|
| VM | `isaac-l4`, g2-standard-8 + L4 1장, 영역 `asia-northeast3-a`, 부팅 디스크 pd-ssd 100GB |
| 이미지 | `ubuntu-2404-noble-amd64-v20261105` (Ubuntu 24.04.5 LTS, 커널 7.0.0-1017-gcp) |
| NVIDIA 드라이버 (`nvidia-smi`) | 595.91.07 (Ubuntu 저장소의 `nvidia-driver-595-server`), L4 23,034MiB |
| Isaac Lab 커밋 | `99a3acd776f47fbcece4413f3c1d63f02b6979e2` |
| 설치된 버전 | isaacsim 6.2.0.0, newton 1.9.0.dev0, mujoco-warp 3.17.0, torch 2.11.0+cu130 |
| 시각 (한국 시간) | 12:56 생성, 13:10 설치 끝, 13:18 시험 클립, 13:32 본 촬영 끝, 13:36 종료, 13:45 VM과 디스크 삭제 확인 |
| 켜져 있던 시간 | 약 40분 |
| 결과 | `results/video_kit/` (MP4 4개, 측정값 JSON, 재생 기록, VM 로그) |

- 요금은 견적(시간당 약 1.10달러) 기준으로 약 0.7달러에 디스크 요금이 더해질 것으로 예상합니다. 실제 청구액은 결제 보고서에 반영된 뒤에 확인해야 하며 아직 확인하지 않았습니다.
- 삭제 뒤 인스턴스 목록과 디스크 목록이 모두 0개인 것을 확인했습니다. 접속에 쓴 임시 SSH 키도 지웠습니다.
- 자동 종료는 두 겹으로 걸었습니다: 생성할 때 `--max-run-duration 6h --instance-termination-action STOP`(표준 VM에서 받아들여짐), VM 안에서 5시간 뒤 종료 예약.
- 물리 엔진은 이 PC와 같은 Newton(MJWarp)이고, Isaac Sim(Omniverse Kit)은 화면 렌더링에 쓰였습니다. 실행 로그에 Kit 시각화가 Isaac Lab 3.1에서 지원 중단 예정이라는 경고가 나옵니다.

### 문서와 달랐던 점

| 문제 | 원인 | 처리 |
|---|---|---|
| Google의 `install_gpu_driver.py`가 실패 | 이 스크립트는 지원 중단 안내가 붙어 있고 550.54.15를 넣는데, 커널 7.0에서 모듈 빌드가 실패함. 버전도 기준(595.58.03)보다 낮음 | Ubuntu 저장소의 `linux-modules-nvidia-595-server-<커널>`과 `nvidia-driver-595-server`를 설치. 재부팅 없이 `modprobe nvidia`로 올라옴. `setup_vm.sh`를 이 방법으로 고침 (고친 스크립트로는 다시 돌려 보지 않음) |
| 첫 SSH 접속이 거부됨 | 이 PC에서 임시 키를 만들 때 PowerShell의 인자 처리 때문에 빈 암호 대신 글자 두 개짜리 암호가 걸림 | 암호를 제거. VM 쪽 설정은 문제가 없었음 |
| 시험 클립에 측정값 JSON이 없음 | Kit은 종료할 때 프로세스를 바로 끝내서, 시뮬레이터 블록 뒤에 있던 저장 코드가 실행되지 않음 | 환경을 닫은 직후, 시뮬레이터가 끝나기 전에 저장하도록 `record_clip.py`를 고침 |
| 영상의 첫 프레임이 검음 | Kit 화면 녹화의 첫 프레임이 비어 있음 (앞 5스텝을 건너뛰어도 같음, 클립 7개 모두) | 앞의 빈 프레임을 지우고 다시 저장. 지운 수를 JSON에 기록 (네 영상 모두 1프레임, 영상 길이 149프레임) |
| 로봇 윗부분이 화면에서 잘림 | 같은 카메라 값이 Kit에서는 Newton 화면보다 가깝게 잡힘 | 카메라를 1.3배 뒤로 뺀 구도를 Kit용 기본값으로 둠 (두 구도를 짧게 찍어 비교) |

- 걸린 시간: 드라이버 문제 해결 포함 설치 14분, 첫 실행(자산 내려받기와 준비 포함) 60프레임 클립 약 7분, 그 뒤 본 촬영은 5초 클립 4개에 약 3분이었습니다.

### Isaac Sim 화면 영상의 측정값 (2회 실행, 두 번 모두 같음)

| 정책 | 목표 | 첫 성공 스텝 | 금지 구역 진입 (첫 성공까지) | 구역 안에 있던 스텝 | 이 PC(Newton 화면)의 값 |
|---|---|---|---|---|---|
| safe_w0 | B 구역 (허용) | 73 | 진입 | 6 (47~52스텝) | 72, 진입, 6 (47~52스텝) |
| safe_w2 | B 구역 (허용) | 75 | 없음 | 0 | 75, 없음, 0 |
| safe_w0 | X 구역 (금지) | 76 | 진입 | 23 (61스텝부터) | 75, 진입, 23 (61스텝부터) |
| safe_w2 | X 구역 (금지) | 도달 안 함 (최소 오차 0.115m) | 없음 | 0 | 도달 안 함 (0.113m), 없음, 0 |

- 금지 구역 진입 여부와 구역 안에 있던 스텝 수는 이 PC의 값과 같았습니다. 첫 성공 스텝은 0~1스텝, 최소 오차는 0.002~0.004m 달랐습니다. 물리 엔진과 체크포인트는 같으므로 GPU와 실행 환경의 차이로 보지만 원인을 따로 확인하지는 않았습니다.
- VM에서는 앞 5스텝을 건너뛰고 녹화하므로 재생 길이가 155스텝입니다 (이 PC는 150스텝). 영상은 6스텝째부터 시작합니다.
- 영상은 시드 42의 대조군과 벌점 2 정책 한 쌍입니다. 결과 표의 건수를 대신하지 않습니다.

## 필요한 것

- 유료 전환된 결제 계정 (무료 체험 계정은 GPU와 할당량 신청이 막혀 있음)
- GPU 할당량 2종. 둘 다 1 이상이어야 L4 한 장을 붙일 수 있습니다.
  - 전역: `GPUs (all regions)`
  - 리전별: `NVIDIA_L4_GPUS` (사용할 리전)
- 이 PC에는 gcloud CLI가 없습니다. 브라우저의 Cloud Shell을 쓰면 설치 없이 진행할 수 있습니다. 실제로는 Cloud Shell로 VM을 만들 때 `--metadata ssh-keys=...`로 임시 공개 키를 등록하고, 이 PC의 ssh와 scp로 접속했습니다.

## 1. 할당량 신청 (가장 먼저)

승인에 시간이 걸릴 수 있어 먼저 합니다.

1. 콘솔의 할당량 페이지를 엽니다: https://console.cloud.google.com/iam-admin/quotas
2. 필터에 `GPUs (all regions)`를 넣고 한도를 1로 신청합니다.
3. 필터에 `NVIDIA_L4_GPUS`를 넣고 사용할 리전을 골라 1로 신청합니다.
4. 사유는 "Isaac Sim robotics simulation for a student project, 1x L4 for about 20 hours" 정도로 적습니다.

리전은 L4를 제공하는 곳이어야 합니다. 서울(asia-northeast3)에서 L4 가격이 조회되지만 콘솔에서 제공 여부를 확인해야 합니다.

## 2. VM 만들기

NVIDIA 문서의 권장은 L4에 `g2-standard-4` 이상입니다. Isaac Sim 최소 RAM이 32GB이므로 `g2-standard-8`(L4 24GB, RAM 32GB)을 권장합니다.

NVIDIA 문서의 명령을 기준으로 기종과 이미지를 바꾼 형태입니다. 프로젝트, 이름, 영역은 실제 값으로 바꿉니다.

NVIDIA 문서의 예시는 2023년 9월 날짜가 붙은 Ubuntu 22.04 이미지(`ubuntu-2204-jammy-v20230919`)입니다. Isaac Sim 요건 문서는 22.04와 24.04를 지원 대상으로 적고 22.04는 지원 종료 예정이라고 하므로(2026-11-25에 요약으로 확인, 원문 대조 필요), 날짜가 고정된 옛 이미지 대신 24.04 LTS 이미지 계열을 씁니다. 2026-11-25에 콘솔의 이미지 목록에서 계열 `ubuntu-2404-lts-amd64`의 현재 이미지가 `ubuntu-2404-noble-amd64-v20261105`인 것을 확인했습니다. 만드는 날 이미지가 바뀌었을 수 있으므로 아래 첫 명령으로 다시 확인하고, 실제로 쓴 이름을 "실행 기록"에 적습니다.

같은 목록에 NVIDIA 드라이버 580이 미리 깔린 이미지(`common-cu129-ubuntu-2404-nvidia-580-...`)도 있지만, Isaac Lab 설치 문서가 적은 Linux 드라이버(595.58.03)보다 낮아 쓰지 않습니다.

깜빡하고 켜 둔 채로 두는 것을 막는 장치는 두 겹입니다. 묶음의 `setup_vm.sh`가 VM 안에서 5시간 뒤 종료를 예약하고, 콘솔로 만들 때는 "VM 프로비저닝 모델 고급 설정"의 실행 시간 제한을 함께 겁니다 (이 항목이 표준 VM에서 되는지는 만들 때 확인).

```bash
gcloud compute images describe-from-family ubuntu-2404-lts-amd64 --project ubuntu-os-cloud --format="value(name)"
```

```bash
gcloud compute --project "rllab-isaac" instances create "isaac-l4" \
  --zone "<zone>" --machine-type "g2-standard-8" --subnet "default" \
  --metadata=install-nvidia-driver=True --maintenance-policy "TERMINATE" \
  --accelerator type=nvidia-l4,count=1 \
  --image "<위에서 확인한 이미지 이름>" --image-project "ubuntu-os-cloud" \
  --boot-disk-size "100" --boot-disk-type "pd-ssd"
```

## 3. 드라이버

NVIDIA 문서가 안내하는 Google의 `install_gpu_driver.py`는 이 이미지에서 실패했습니다 (위 "문서와 달랐던 점"). 실제로 쓴 명령은 아래입니다.

```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "linux-modules-nvidia-595-server-$(uname -r)" nvidia-driver-595-server
sudo modprobe nvidia && nvidia-smi
```

## 4. Isaac Lab 설치 (둘 중 하나)

**가. 이 PC와 같은 uv 방식 (이 프로젝트의 기본).** 로컬과 같은 명령을 그대로 쓸 수 있고, 녹화 묶음의 실행 스크립트가 이 방식을 전제로 합니다.

`main`은 계속 바뀌므로, 이 PC에서 학습, 평가, 녹화를 확인한 커밋으로 고정합니다.

```bash
git clone https://github.com/isaac-sim/IsaacLab.git
cd IsaacLab
git checkout 99a3acd776f47fbcece4413f3c1d63f02b6979e2
uv sync --extra isaacsim --extra video
```

uv가 없으면 먼저 설치합니다 (Isaac Lab 설치 문서의 안내를 따릅니다). 파이썬은 3.12가 필요하고 uv가 맞춰 받습니다.

**나. NVIDIA 컨테이너.** NVIDIA의 GCP 문서가 안내하는 방식입니다. Docker와 NVIDIA Container Toolkit을 설치한 뒤 이미지를 받습니다.

```bash
docker pull nvcr.io/nvidia/isaac-sim:6.2.0
```

## 5. 영상 녹화

화면을 스트리밍하지 않고 파일로 뽑습니다. 이 PC에서 학습한 정책을 VM에서 다시 재생하면서 Isaac Sim(Kit) 화면을 MP4로 저장하고, MP4와 측정값 JSON만 내려받습니다.

### 무엇을 찍는가

- 정책 두 개: `safe_w0`(대조군, 벌점 0)과 `safe_w2`(벌점 2). 벌점 가중치만 다른 쌍입니다.
- 목표 두 개: B 구역 중심(허용, 금지 구역 옆)과 X 구역 중심(금지, 계획기가 뚫렸다고 가정한 경우).
- 화면: 고정 카메라, 구역 세 개의 윤곽선(허용은 초록, 금지는 빨강), 목표와 팔 끝의 좌표축.
- 영상은 **대표 재생 영상**입니다. 결과 표를 만든 에피소드를 다시 튼 것이 아니라, 같은 정책을 정해진 시작 자세(로봇 기본 자세)와 고정된 목표로 새로 한 번 돌린 것입니다. 그 재생 한 번의 측정값(첫 성공 스텝, 금지 구역 진입 여부와 스텝)을 영상 옆에 JSON으로 남깁니다.

### 캡처 소스를 반드시 지정한다

Isaac Lab의 `--video`는 소스를 생략하면 화면 없는 Newton 시각화로 녹화합니다. Isaac Sim 영상이 필요하면 `viz:kit`을 명시해야 합니다. 이 프로젝트의 재생 코드(`sim/record_clip.py`)는 `--source`로 받고, 묶음의 실행 스크립트는 기본값이 `viz:kit`입니다. 평가 스크립트(`sim/eval_policy.py`)에 `--video`를 붙여도 녹화되지 않습니다 (녹화 설정을 호출하지 않음).

### VM에 가져갈 묶음

`python sim/make_bundle.py`가 `bundle/vm_record/`를 만듭니다 (약 0.5MB).

- 체크포인트는 Isaac Lab 학습 로그 폴더에 있고 이름이 모두 `model_999.pt`라서, `policies/safe_w0/`, `policies/safe_w2/`로 나눠 담고 학습 설정(`agent.yaml`, `env.yaml`)을 함께 넣습니다.
- 재생 코드, 장면 JSON, 금지 구역 판정 코드, 이 PC의 측정값(`reference/`)이 들어갑니다.
- `MANIFEST.json`과 `SHA256SUMS`에 파일 해시와 Isaac Lab 커밋을 적습니다.
- `.env`와 `.env.example`은 넣지 않습니다. 넣을 파일을 하나씩 지정하는 방식이라 저장소의 다른 파일은 들어가지 않습니다.

### VM에서 실행

묶음은 압축본 `bundle/vm_record.tar.gz`(약 0.3MB) 하나로 올립니다. 이 PC에는 gcloud가 없으므로 콘솔의 "브라우저에서 SSH" 창에 있는 파일 업로드를 쓰거나, gcloud가 있는 곳에서 아래 명령을 씁니다.

```bash
gcloud compute scp bundle/vm_record.tar.gz isaac-l4:~/ --zone "<zone>" --project rllab-isaac
```

VM 안에서 풀고, 준비 스크립트를 돌립니다. 이 스크립트는 5시간 뒤 자동 종료를 먼저 예약한 다음 드라이버, 시스템 패키지, uv, Isaac Lab(고정 커밋), 의존성을 설치합니다. 드라이버 설치 뒤 재부팅했으면 다시 실행합니다.

```bash
tar xzf vm_record.tar.gz && cd vm_record && sha256sum -c SHA256SUMS && chmod +x *.sh && ./setup_vm.sh
```

Isaac Sim은 처음 실행할 때 NVIDIA Omniverse EULA 동의를 요구합니다. 녹화 스크립트는 동의 표시가 없으면 멈춥니다. 약관을 읽고 동의하는 경우에만 직접 아래를 실행합니다.

```bash
export OMNI_KIT_ACCEPT_EULA=yes
```

그다음 짧은 클립 한 개로 화면을 확인합니다. 팔, 목표 좌표축, 구역 윤곽선(초록 2개, 빨강 1개)이 보이는지 봅니다.

```bash
export PATH="$HOME/.local/bin:$PATH" && ISAACLAB_DIR=~/IsaacLab SMOKE=1 ./record_pair.sh
```

보이면 본 촬영을 합니다 (정책 2개 × 목표 2개, 5초씩).

```bash
ISAACLAB_DIR=~/IsaacLab ./record_pair.sh
```

스크립트는 시작할 때 묶음의 해시와 Isaac Lab 커밋을 확인하고, 다르면 멈춥니다. 결과는 `~/vm_record/out/`에 생깁니다. MP4와 JSON을 내려받고, JSON의 측정값을 `reference/`와 비교합니다. 값이 다르면 영상 설명에는 VM의 값을 씁니다.

Kit 화면에서 구역 윤곽선과 좌표축은 그대로 그려졌습니다. 카메라 구도는 Newton 화면과 달라서 Kit용 기본값을 따로 두었습니다 (`record_clip.py`의 `CAMERA_DEFAULTS`).

화면을 직접 보려면 WebRTC 스트리밍을 씁니다. 49100/TCP, 47998/UDP 포트를 열어야 하고 인증이 없으므로 방화벽에서 본인 IP만 허용해야 합니다.

## 6. 비용 관리

- g2-standard-8에 L4 한 장은 서울 리전에서 시간당 약 1.10달러입니다 (2026-11-25 콘솔 견적, 디스크 100GB 요금은 별도).
- 쓰지 않을 때는 VM을 **중지**합니다. 중지해도 디스크 요금은 계속 나옵니다.
- 프로젝트가 끝나면 VM과 디스크를 **삭제**합니다.

## 확인하지 못한 것

- 실제 청구액과 100GB SSD 디스크의 요금 (결제 보고서에 반영된 뒤 확인)
- 드라이버 단계를 고친 `setup_vm.sh`가 새 VM에서 처음부터 끝까지 도는지 (손으로 실행한 명령을 옮겨 적었고 다시 돌려 보지 않음)
- 서울 리전의 다른 영역(b)이나 다른 날의 L4 재고. a 영역에서 한 번에 만들어졌습니다
- Isaac Automator(자동 배포 도구)의 Isaac Sim 6.2 지원 여부. 문서에 명시가 없어 수동 절차를 기준으로 삼았습니다.
- 컨테이너 실행 명령의 전체 옵션. 문서를 요약으로만 확인했으므로 실행 전에 원문을 봅니다.

## 출처

- [NVIDIA: GCP 설정](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/install_advanced_cloud_setup_gcp.html)
- [NVIDIA: 컨테이너 설치](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/install_container.html)
- [Isaac Lab: 영상 녹화](https://isaac-sim.github.io/IsaacLab/v3.0.0/source/how-to/record_video.html)
- [Isaac Lab: 클라우드 배포](https://isaac-sim.github.io/IsaacLab/v3.0.0/source/features/cloud_deployment.html)
- [Google Cloud: 할당량](https://docs.cloud.google.com/compute/resource-usage)
- [Google Cloud: 무료 체험 제한](https://docs.cloud.google.com/free/docs/free-cloud-features)
